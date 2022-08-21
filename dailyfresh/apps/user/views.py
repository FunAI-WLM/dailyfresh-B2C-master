# -*-coding:utf-8-*-
from django.shortcuts import render, redirect
from django.urls import reverse
from django.core.mail import send_mail
from django.contrib.auth import authenticate, login, logout
from django.core.paginator import Paginator
from django.views.generic import View
from django.http import HttpResponse
from django.conf import settings

from apps.user.models import User, Address
from apps.goods.models import GoodsSKU
from apps.goods.models import Goods
from apps.goods.models import GoodsType
from apps.goods.models import IndexPromotionBanner
from apps.goods.models import IndexGoodsBanner
from apps.goods.models import IndexTypeGoodsBanner
from apps.order.models import OrderInfo, OrderGoods

from celery_tasks.tasks import send_register_active_email
from itsdangerous import TimedJSONWebSignatureSerializer as Serializer
from itsdangerous import SignatureExpired
# from dailyfresh.apps.goods.models import Goods
from utils.mixin import LoginRequiredMixin
from django_redis import get_redis_connection
import re
import time
from django.db.models import Count


# /user/register
def register(request):
    """注册"""
    if request.method == 'GET':
        return render(request, 'df_user/register.html')  # 显示注册页面
    else:
        # 进行注册处理
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'df_user/register.html', {'errmsg': '数据不完整'})

        # 检验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'df_user/register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'df_user/register.html', {'errmsg': '请同意协议'})

        # 校验用户是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            return render(request, 'df_user/register.html', {'errmsg': '用户已存在'})

        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 返回应答,跳转首页
        return redirect(reverse('goods:index'))


class RegisterView(View):
    """注册"""
    def get(self, request):
        # 显示注册页面
        return render(request, 'df_user/register.html')

    def post(self, request):
        # 进行注册处理
        # 接收数据
        username = request.POST.get('user_name')
        password = request.POST.get('pwd')
        email = request.POST.get('email')
        allow = request.POST.get('allow')

        # 进行数据校验
        if not all([username, password, email]):
            # 数据不完整
            return render(request, 'df_user/register.html', {'errmsg': '数据不完整'})

        # 检验邮箱
        if not re.match(r'^[a-z0-9][\w.\-]*@[a-z0-9\-]+(\.[a-z]{2,5}){1,2}$', email):
            return render(request, 'df_user/register.html', {'errmsg': '邮箱格式不正确'})

        if allow != 'on':
            return render(request, 'df_user/register.html', {'errmsg': '请同意协议'})

        # 校验用户是否重复
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            # 用户名不存在
            user = None

        if user:
            return render(request, 'df_user/register.html', {'errmsg': '用户已存在'})

        # 进行业务处理：进行用户注册
        user = User.objects.create_user(username, email, password)
        user.is_active = 0
        user.save()

        # 发送激活链接，包含激活链接：http://127.0.0.1:8000/user/active/5
        # 激活链接中需要包含用户的身份信息，并要把身份信息进行加密
        # 激活链接格式: /user/active/用户身份加密后的信息 /user/active/token

        # 加密用户的身份信息，生成激活token
        serializer = Serializer(settings.SECRET_KEY, 3600)
        info = {'confirm': user.id}
        token = serializer.dumps(info)  # bytes
        token = token.decode('utf8')  # 解码, str

        # 发邮箱
        # subject = '天天生鲜欢迎信息'
        # message = ''
        # sender = settings.EMAIL_PROM  # 发送人
        # receiver = [email]
        # html_message = '<h1>%s, 欢迎您成为天天生鲜注册会员' \
        #                '</h1>请点击下面链接激活您的账户<br/>' \
        #                '<a href="http://127.0.0.1:8000/user/active/%s">' \
        #                'http://127.0.0.1:8000/user/active/%s' \
        #                '</a>' % (username, token, token)
        #
        # send_mail(subject, message, sender, receiver, html_message=html_message)

        # 找其他人帮助我们发送邮件 celery:异步执行任务
        send_register_active_email.delay(email, username, token)

        # 返回应答,跳转首页
        return redirect(reverse('goods:index'))


# /user/active/加密信息token
class ActiveView(View):
    """用户激活"""
    def get(self, request, token):
        # 进行用户激活
        # 进行解密，获取要激活的用户信息
        serializer = Serializer(settings.SECRET_KEY, 3600)
        try:
            info = serializer.loads(token)
            # 获取待激活用户的id
            user_id = info['confirm']

            # 根据id获取用户信息
            user = User.objects.get(id=user_id)
            user.is_active = 1
            user.save()

            # 跳转到登录页面
            return redirect(reverse('user:login'))
        except SignatureExpired as e:
            # 激活链接已过期
            return HttpResponse('激活链接已失效')


# /user/login
class LoginView(View):
    """登录"""
    def get(self, request):
        # 显示登录页面
        # 判断是否记住密码
        if 'username' in request.COOKIES:
            username = request.COOKIES.get('username')  # request.COOKIES['username']
            checked = 'checked'
        else:
            username = ''
            checked = ''

        return render(request, 'df_user/login.html', {'username': username, 'checked': checked})

    def post(self, request):
        # 接受数据
        username = request.POST.get('username')
        password = request.POST.get('pwd')
        # remember = request.POST.get('remember')  # on

        # 校验数据
        if not all([username, password]):
            return render(request, 'df_user/login.html', {'errmsg': '数据不完整'})


        # type = models.ForeignKey('GoodsType', on_delete=models.CASCADE, verbose_name='商品种类')
        # goods = models.ForeignKey('Goods', on_delete=models.CASCADE, verbose_name='商品SPU')
        # name = models.CharField(max_length=20, verbose_name='商品名称')
        # desc = models.CharField(max_length=256, verbose_name='商品简介')
        # price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='价格')
        # unite = models.CharField(max_length=20, verbose_name='商品单位')
        # image = models.ImageField(upload_to='goods', verbose_name='商品图片')
        # stock = models.IntegerField(default=1, verbose_name='商品库存')
        # sales = models.IntegerField(default=0, verbose_name='商品销量')
        # status = models.SmallIntegerField(default=1, choices=status_choices, verbose_name='状态')

        # name = "goods009_d_xj"
        # Goods.objects.create(name=name)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=7)
        # name = "slide海鲜"
        # desc = "slide海鲜"
        # price = 0.0
        # unite = "个"
        # image = "/static/images/slide04_haixian.jpg"
        # stock = 100
        # sales = 20
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)
 
        # /static/images/adv02.jpg
        # /static/images/adv01.jpg

        # name = "吃货暑假趴"
        # url = "#"
        # image = "/static/images/adv02_lefttop.jpg"
        # index = 2
        # IndexPromotionBanner.objects.create(name=name,url=url,image=image,index=index)

        # sku = GoodsSKU.objects.get(id=4)
        # image = "/static/images/slide04_haixian.jpg"
        # index = 4
        # IndexGoodsBanner.objects.create(sku=sku,image=image,index=index)

        # type = GoodsType.objects.get(id=4)
        # goods = Goods.objects.get(id=14)
        # name = "海鲜水产"
        # desc = "海鲜水产"
        # price = 100.0
        # unite = "斤"
        # image = "static/images/banner02_haixianshengyan.jpg"
        # stock = 100
        # sales = 20
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=13)
        # name = "新鲜水果"
        # desc = "新鲜水果"
        # price = 20.0
        # unite = "斤"
        # image = "static/images/banner01_shilingshuoguo.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=6)
        # goods = Goods.objects.get(id=15)
        # name = "猪牛羊肉"
        # desc = "猪牛羊肉"
        # price = 20.0
        # unite = "斤"
        # image = "static/images/banner03_xinxiantegong.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=7)
        # goods = Goods.objects.get(id=16)
        # name = "禽类蛋品"
        # desc = "禽类蛋品"
        # price = 10.0
        # unite = "斤"
        # image = "static/images/banner04_yuandichuchan.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=8)
        # goods = Goods.objects.get(id=17)
        # name = "新鲜蔬菜"
        # desc = "新鲜蔬菜"
        # price = 10.0
        # unite = "斤"
        # image = "static/images/banner05_lvseyouji.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=9)
        # goods = Goods.objects.get(id=18)
        # name = "速冻食品"
        # desc = "速冻食品"
        # price = 9.0
        # unite = "斤"
        # image = "static/images/banner06_shuangkubingpin.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=4)
        # sku = GoodsSKU.objects.get(id=5)
        # display_type = 1
        # index = 1
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=5)
        # sku = GoodsSKU.objects.get(id=6)
        # display_type = 1
        # index = 2
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=6)
        # sku = GoodsSKU.objects.get(id=7)
        # display_type = 1
        # index = 3
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=7)
        # sku = GoodsSKU.objects.get(id=8)
        # display_type = 1
        # index = 4
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=8)
        # sku = GoodsSKU.objects.get(id=9)
        # display_type = 1
        # index = 5
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)


        # type = GoodsType.objects.get(id=9)
        # sku = GoodsSKU.objects.get(id=10)
        # display_type = 1
        # index = 6
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)


        # type = GoodsType.objects.get(id=4)
        # goods = Goods.objects.get(id=25)
        # name = "龙虾"
        # desc = "龙虾"
        # price = 140.0
        # unite = "斤"
        # image = "static/images/goods/goods023_longlongxia.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=4)
        # goods = Goods.objects.get(id=26)
        # name = "秋刀鱼"
        # desc = "秋刀鱼"
        # price = 40.0
        # unite = "斤"
        # image = "static/images/goods/goods022_qiudaoyu.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=4)
        # goods = Goods.objects.get(id=27)
        # name = "基围虾"
        # desc = "基围虾"
        # price = 70.0
        # unite = "斤"
        # image = "static/images/goods/goods020_xia.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=4)
        # goods = Goods.objects.get(id=28)
        # name = "扇贝"
        # desc = "扇贝"
        # price = 70.0
        # unite = "斤"
        # image = "static/images/goods/goods021_shanbei.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=29)
        # name = "草莓"
        # desc = "草莓"
        # price = 80.0
        # unite = "斤"
        # image = "static/df_goods/goods003_d_caomei.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=30)
        # name = "奇异果"
        # desc = "奇异果"
        # price = 10.0
        # unite = "斤"
        # image = "static/df_goods/goods012_d_qiyiguo.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=31)
        # name = "橘子"
        # desc = "橘子"
        # price = 10.0
        # unite = "斤"
        # image = "static/df_goods/goods013_d_juzi.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=5)
        # goods = Goods.objects.get(id=32)
        # name = "香蕉"
        # desc = "香蕉"
        # price = 5.0
        # unite = "斤"
        # image = "static/df_goods/goods009_d_xj.jpg"
        # stock = 100
        # sales = 50
        # status = 0
        # GoodsSKU.objects.create(type=type,goods=goods,name=name,desc=desc,price=price,unite=unite,image=image,stock=stock,
        # sales=sales,status=status)

        # type = GoodsType.objects.get(id=4)
        # sku = GoodsSKU.objects.get(id=11)
        # display_type = 1
        # index = 7
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=4)
        # sku = GoodsSKU.objects.get(id=13)
        # display_type = 1
        # index = 8
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=4)
        # sku = GoodsSKU.objects.get(id=15)
        # display_type = 1
        # index = 9
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=4)
        # sku = GoodsSKU.objects.get(id=16)
        # display_type = 1
        # index = 10
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=5)
        # sku = GoodsSKU.objects.get(id=17)
        # display_type = 1
        # index = 11
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=5)
        # sku = GoodsSKU.objects.get(id=18)
        # display_type = 1
        # index = 12
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=5)
        # sku = GoodsSKU.objects.get(id=19)
        # display_type = 1
        # index = 13
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)

        # type = GoodsType.objects.get(id=5)
        # sku = GoodsSKU.objects.get(id=25)
        # display_type = 1
        # index = 14
        # IndexTypeGoodsBanner.objects.create(type=type,sku=sku,display_type=display_type,index=index)


















        # 业务处理: 登陆校验
        user = authenticate(username=username, password=password)
        if user is not None:
            if user.is_active:
                # print("User is valid, active and authenticated")
                login(request, user)  # 登录并记录用户的登录状态

                # 获取登录后所要跳转到的地址, 默认跳转首页
                next_url = request.GET.get('next', reverse('goods:index'))

                #  跳转到next_url
                response = redirect(next_url)  # HttpResponseRedirect

                # 设置cookie, 需要通过HttpReponse类的实例对象, set_cookie
                # HttpResponseRedirect JsonResponse

                # 判断是否需要记住用户名
                remember = request.POST.get('remember')
                if remember == 'on':
                    response.set_cookie('username', username, max_age=7*24*3600)
                else:
                    response.delete_cookie('username')

                # 回应 response
                return response

            else:
                # print("The passwoed is valid, but the account has been disabled!")
                return render(request, 'df_user/login.html', {'errmsg': '账户未激活'})
        else:
            return render(request, 'df_user/login.html', {'errmsg': '用户名或密码错误'})


# /user/logout
class LogoutView(View):
    """退出登录"""
    def get(self, request):
        logout(request)

        return redirect(reverse('goods:index'))


# itemgetter 用于获取对象的哪些位置的数据，参数即为代表位置的序号值
from operator import itemgetter
# from db import select

# 将购买过good_id的用户及其购物信息筛选出来
def get_data(good_id):
    pass
    # sql = 'SELECT u_g.userId, u_g.goodsId, g.img, g.title, g.eva_num FROM user_goods u_g, goods g WHERE userId in (SELECT userId FROM user_goods WHERE goodsId = %d) AND u_g.goodsId = g.id' %good_id
    # result = select(sql)
    # data = {}                                        # 数据矩阵
    # for row in result:                               # 遍历result，将数据以字典的形式存储到data中
    #     if row[0] not in data:                       # 如果data中没有这用户，则将这个用户添加进去
    #         data[row[0]] = []
    #     data[row[0]].append({'id':row[1],'img': row[2],'title': row[3],'eva_num': row[4]})
    # # print(data)
    # return data                                      # data 的结构与下面注释的data的结构近似

# 购买过此商品的用户还购买过——推荐算法
def recommend_goods_based(good_id, count):
    data = get_data(good_id)
    goods_count = {}                                # 统计每个商品出现的次数
    goods_data = []                                 # 统计每个商品的信息
    for user in data.keys():                        # 遍历大字典，用户为键，商品信息为值
        for good in data[user]:                     # 遍历小字典
            if good['id'] == good_id:               # 如果与已给出的商品相同，则退出此次循环，查看下一个
                continue
            if good['id'] not in goods_count:       # 如果这个商品没在goods_count中，则添加给物品，默认出现次数为0
                goods_count.setdefault(good['id'], 0)
            goods_count[good['id']] += 1            # 将这个商品的出现次数+1 
            if good['id'] not in goods_data:        #如果这个商品不在goods_data中，则添加这个商品
                goods_data.append(good)
    # print('商品出现的频次', goods_count)
    if count < len(goods_count):                    # 需要推荐的商品个数小于 len(goods_count)，则推荐前count个
        goods_count_sort = sorted(goods_count.items(), key=itemgetter(1), reverse=True)[:count]
    else:                                           # 需要推荐的商品个数大于 len(goods_count)，则推荐goods_count里的所有商品
        goods_count_sort = goods_count
    # print('商品出现的频次排序', goods_count_sort)
    count_sort = []
    for good_id in goods_count_sort:                # 统计待推荐的商品序号
        count_sort.append(good_id[0])
    print('所要推荐的商品的序号', count_sort)
    # print('商品信息数据', goods_data, end='\n')
    # print('要推荐的商品信息')
    recommend_goods = []                            # 存储要推荐的商品
    for id in count_sort:                           # 统计要推荐的商品的信息
        for good in goods_data:
            if id == good['id'] and good not in recommend_goods:
                # print('item', good)
                recommend_goods.append(good)
    return recommend_goods

# if __name__ == '__main__':
#     # get_data(1)
#     for good in recommend_goods_based(1, 6):                   # 推荐6个与商品1相似的商品
#         print(good)

# /user
class UserInfoView(LoginRequiredMixin, View):
    """用户中心-信息页"""
    def get(self, request):
        # 获取个人信息
        user = request.user
        address = Address.objects.get_default_address(user)

        # 获取用户的历史浏览记录
        # from redis import StrictRedis
        # sr = StrictRedis(host='127.0.0.1', port='6379', db=9)
        con = get_redis_connection('default')

        history_key = 'history_%d' % user.id

        # 获取用户最新历史浏览记录的5个商品id
        sku_ids = con.lrange(history_key, 0, 4)

        # 从数据库中查询用户浏览商品的具体信息
        # goods_li = GoodsSKU.objects.filter(id__in=sku_ids)
        #
        # goods_res = []
        # for a_id in sku_ids:
        #     for goods in goods_li:
        #         goods_res.append(goods)

        # 遍历获取用户浏览的历史商品信息
        goods_list = []
        # for id in sku_ids:
        #     goods = GoodsSKU.objects.get(id=id)
        #     goods.url=goods.image.url[25:]
        #     goods_list.append(goods)

        goods_list_temp = GoodsSKU.objects.filter(type_id=5)
        for item in goods_list_temp:
            item.url=item.image.url[25:]
            goods_list.append(item)

        # ,user_id != user.id
        sku_id_first = sku_ids[0]
        Order_Info_list = []
        user_id_list = []
        # Order_Goods_order_ids = OrderGoods.objects.filter(sku_id=sku_id_first).all()
        # print("222222    Order_Goods_order_ids  {} ".format(len(Order_Goods_order_ids)))
        # for Order_Goods_order_id in Order_Goods_order_ids:
        #     order_id = Order_Goods_order_id.order_id
        #     Order_Info = OrderInfo.objects.get(order_id=order_id)
        #     Order_Info_list.append(Order_Info)
        # for Order_Info_item in Order_Info_list:
        #     if user.id != Order_Info_item.user_id:
        #         user_id_list.append(Order_Info_item.user_id)
    
        # data = {}                                        # 数据矩阵
        # Order_Info_group_by = OrderInfo.objects.values("user_id").annotate(count=Count("order_id")).all()
        # for Order_Info_item in Order_Info_group_by:
        #     if Order_Info_item.order_id not in data:                       # 如果data中没有这用户，则将这个用户添加进去
        #         data[Order_Info_item.order_id] = []
        #     data[Order_Info_item.order_id].append({'user_id':Order_Info_item.user_id,'count':Order_Info_item.count})
        # for order_id in data.keys():                        # 遍历大字典，用户为键，商品信息为值
        #    for good in data[order_id]:
        #      Order_Goods = OrderGoods.objects.get(order_id=order_id) 
        #      sku_id_list = []
        #      for Order_Good in Order_Goods:
        #         sku_id_list.append(Order_Good.sku_id)
        #         data[Order_Info_item.order_id].append({'sku_id_list':sku_id_list})
       

                
        
        




        # 组织上下文
        context = {'page': 'user',
                   'address': address,
                   'goods_list': goods_list}

        return render(request, 'df_user/user_center_info.html', context)


# /user/order
class UserOrderView(LoginRequiredMixin, View):
    """用户中心-订单页"""
    def get(self, request, page):
        # 获取用户的订单信息
        user = request.user
        orders = OrderInfo.objects.filter(user=user).order_by('-create_time')

        # 遍历获取订单商品信息
        for order in orders:
            # 根据order_id查询订单商品信息
            order_skus = OrderGoods.objects.filter(order_id=order.order_id)

            # 遍历Order_skus计算商品的小计
            for order_sku in order_skus:
                amount = order_sku.count * order_sku.price
                # 动态给order_sku增加属性amount,保存订单商品小计
                order_sku.amount = amount

            # 动态给order增加属性, 保存订单状态标题
            order.status_name = OrderInfo.ORDER_STATUS[order.order_status]
            order.order_skus = order_skus
            for order_sku in order.order_skus:
                order_sku.sku = GoodsSKU.objects.get(id=order_sku.sku_id)
                order_sku.sku.url=order_sku.sku.image.url[25:]
                
        # 分页
        paginator = Paginator(orders, 2)  # 单页显示数目2

        try:
            page = int(page)
        except Exception as e:
            page = 1

        if page > paginator.num_pages or page <= 0:
            page = 1

        # 获取第page页的Page实例对象
        order_page = paginator.page(page)

        # todo: 进行页码的控制，页面上最多显示5个页码
        # 1. 总数不足5页，显示全部
        # 2. 如当前页是前3页，显示1-5页
        # 3. 如当前页是后3页，显示后5页
        # 4. 其他情况，显示当前页的前2页，当前页，当前页的后2页
        num_pages = paginator.num_pages
        if num_pages < 5:
            pages = range(1, num_pages)
        elif page <= 3:
            pages = range(1, 6)
        elif num_pages - page <= 2:
            pages = range(num_pages-4, num_pages+1)
        else:
            pages = range(page-2, page+3)

        # 组织上下文
        context = {'order_page': order_page,
                   'pages': pages,  # 页面范围控制
                   'page': 'order'}

        return render(request, 'df_user/user_center_order.html', context)


# /user/address
class AddressView(LoginRequiredMixin, View):
    """用户中心-地址页"""
    def get(self, request):
        # django框架会给request对象添加一个属性user
        # 如果用户已登录，user的类型User
        # 如果用户没登录，user的类型AnonymousUser
        # 除了我们给django传递的模板变量，django还会把user传递给模板文件

        # 获取用户的默认地址
        # 获取登录用户对应User对象
        user = request.user

        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None  # 不存在默认地址
        address = Address.objects.get_default_address(user)

        return render(request, 'df_user/user_center_site.html', {'title': '用户中心-收货地址', 'page': 'address', 'address': address})

    def post(self, request):
        # 地址添加
        receiver = request.POST.get('receiver')
        addr = request.POST.get('addr')
        zip_code = request.POST.get('zip_code')
        phone = request.POST.get('phone')

        # 业务处理：地址添加
        # 如果用户没存在默认地址，则添加的地址作为默认收获地址
        user = request.user

        # try:
        #     address = Address.objects.get(user=user, is_default=True)
        # except Address.DoesNotExist:
        #     address = None  # 不存在默认地址
        address = Address.objects.get_default_address(user)

        if address:
            is_default = False
        else:
            is_default = True

        # 数据校验
        if not all([receiver, addr, phone]):
            return render(request, 'df_user/user_center_site.html',
                          {'page': 'address',
                           'address': address,
                           'errmsg': '数据不完整'})

        # 校验手机号
        if not re.match(r'^1([3-8][0-9]|5[189]|8[6789])[0-9]{8}$', phone):
            return render(request, 'df_user/user_center_site.html',
                          {'page': 'address',
                           'address': address,
                           'errmsg': '手机号格式不合法'})

        # 添加
        Address.objects.create(user=user,
                               receiver=receiver,
                               addr=addr,
                               zip_code=zip_code,
                               phone=phone,
                               is_default=is_default)

        # 返回应答
        return redirect(reverse('user:address'))  # get的请求方式
